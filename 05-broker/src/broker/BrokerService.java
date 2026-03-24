package broker;

import java.rmi.RemoteException;
import java.rmi.server.UnicastRemoteObject;
import java.time.LocalTime;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class BrokerService extends UnicastRemoteObject implements BrokerRemote {
    public static final String STATUS_GRAY = "gray";
    public static final String STATUS_BLUE = "blue";
    public static final String STATUS_ORANGE = "orange";
    public static final String STATUS_RED = "red";

    private static final DateTimeFormatter CLOCK = DateTimeFormatter.ofPattern("HH:mm:ss");

    private final Object lock = new Object();
    private final Map<String, SaleStatus> bySale = new HashMap<>();

    public BrokerService() throws RemoteException {
        super();
    }

    @Override
    public void serverRegistered(String saleId, String serverHost, int serverPort, int expectedClients) {
        if (saleId == null || saleId.isBlank()) {
            return;
        }
        synchronized (lock) {
            SaleStatus state = bySale.computeIfAbsent(saleId, this::newSale);
            state.server = serverHost + ":" + serverPort;
            state.expectedClients = Math.max(0, expectedClients);
            state.status = STATUS_BLUE;
            state.updatedAt = now();
            System.out.println("[Broker] SERVER_REGISTERED sale=" + saleId + " server=" + state.server + " expectedClients=" + state.expectedClients);
        }
    }

    @Override
    public void clientConnected(String saleId, String clientId, int buyers) {
        if (saleId == null || saleId.isBlank()) {
            return;
        }
        synchronized (lock) {
            SaleStatus state = bySale.computeIfAbsent(saleId, this::newSale);
            state.connectedClients += 1;
            state.buyerThreads += Math.max(0, buyers);
            if (!STATUS_RED.equals(state.status)) {
                state.status = STATUS_BLUE;
            }
            state.updatedAt = now();
            System.out.println("[Broker] CLIENT_CONNECTED sale=" + saleId + " client=" + clientId + " connected=" + state.connectedClients + "/" + state.expectedClients);
        }
    }

    @Override
    public void salesProgress(String saleId, int soldSeats, int totalSeats) {
        if (saleId == null || saleId.isBlank()) {
            return;
        }
        synchronized (lock) {
            SaleStatus state = bySale.computeIfAbsent(saleId, this::newSale);
            state.soldSeats = Math.max(0, soldSeats);
            state.totalSeats = Math.max(0, totalSeats);
            if (!STATUS_RED.equals(state.status) && state.connectedClients > 0 && state.soldSeats > 0) {
                state.status = STATUS_ORANGE;
            }
            state.updatedAt = now();
        }
    }

    @Override
    public void serverFinished(String saleId, String summary) {
        if (saleId == null || saleId.isBlank()) {
            return;
        }
        synchronized (lock) {
            SaleStatus state = bySale.computeIfAbsent(saleId, this::newSale);
            state.status = STATUS_RED;
            state.summary = summary == null ? "" : summary;
            state.updatedAt = now();
            System.out.println("[Broker] SERVER_FINISHED sale=" + saleId + " summary=" + state.summary);
        }
    }

    @Override
    public BrokerSnapshot getSnapshot() {
        synchronized (lock) {
            BrokerSnapshot snapshot = new BrokerSnapshot();
            List<SaleStatus> sales = new ArrayList<>();
            for (SaleStatus sale : bySale.values()) {
                sales.add(sale.copy());
            }
            sales.sort(Comparator.comparing(x -> x.saleId));
            snapshot.sales = sales;
            return snapshot;
        }
    }

    private SaleStatus newSale(String saleId) {
        SaleStatus status = new SaleStatus();
        status.saleId = saleId;
        status.status = STATUS_GRAY;
        status.server = "-";
        status.expectedClients = 0;
        status.connectedClients = 0;
        status.buyerThreads = 0;
        status.soldSeats = 0;
        status.totalSeats = 0;
        status.updatedAt = now();
        status.summary = "";
        return status;
    }

    private static String now() {
        return LocalTime.now().format(CLOCK);
    }
}
