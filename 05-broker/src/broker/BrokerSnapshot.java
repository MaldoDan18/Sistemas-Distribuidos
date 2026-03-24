package broker;

import java.io.Serializable;
import java.util.ArrayList;
import java.util.List;

public class BrokerSnapshot implements Serializable {
    private static final long serialVersionUID = 1L;

    public List<SaleStatus> sales = new ArrayList<>();
}
