package broker;

import java.io.Serializable;

public class SaleStatus implements Serializable {
    private static final long serialVersionUID = 1L;

    public String saleId;
    public String status;
    public String server;
    public int expectedClients;
    public int connectedClients;
    public int buyerThreads;
    public String updatedAt;
    public String summary;

    public SaleStatus copy() {
        SaleStatus other = new SaleStatus();
        other.saleId = this.saleId;
        other.status = this.status;
        other.server = this.server;
        other.expectedClients = this.expectedClients;
        other.connectedClients = this.connectedClients;
        other.buyerThreads = this.buyerThreads;
        other.updatedAt = this.updatedAt;
        other.summary = this.summary;
        return other;
    }
}
